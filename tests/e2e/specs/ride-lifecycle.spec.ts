import { expect, test, type Browser, type Page } from '@playwright/test'
import {
  createTestUser,
  deleteTestUser,
  signInAs,
  type TestUser,
} from '../support/clerk-users'

const FROM = { address: 'Dizengoff Square, Tel Aviv, Israel', lat: 32.0779, lng: 34.7744 }
const TO = { address: 'Azrieli Center, Tel Aviv, Israel', lat: 32.0745, lng: 34.7918 }

/** Answers the frontend's Mapbox Geocoding v6 lookup so runs never depend on Mapbox. */
async function stubMapbox(page: Page) {
  await page.route('https://api.mapbox.com/search/geocode/v6/forward*', async (route) => {
    const query = new URL(route.request().url()).searchParams.get('q') ?? ''
    const place = query.toLowerCase().startsWith('diz') ? FROM : TO
    await route.fulfill({
      json: {
        type: 'FeatureCollection',
        features: [
          {
            id: place.address,
            geometry: { type: 'Point', coordinates: [place.lng, place.lat] },
            properties: {
              mapbox_id: place.address,
              name: place.address.split(',')[0],
              full_address: place.address,
              place_formatted: 'Tel Aviv, Israel',
              coordinates: { latitude: place.lat, longitude: place.lng },
            },
          },
        ],
      },
    })
  })
}

/** `YYYY-MM-DDTHH:mm` in local time, which is what a datetime-local input takes. */
function localInputValue(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`
}

async function pickAddress(page: Page, label: string, typed: string, address: string) {
  await page.getByLabel(label, { exact: true }).fill(typed)
  await page.getByRole('option', { name: new RegExp(address.split(',')[0]) }).click()
}

async function onboard(page: Page, user: TestUser, withCar: boolean) {
  await expect(page.getByRole('heading', { name: 'Set up your profile' })).toBeVisible()
  await page.getByLabel('Name').fill(user.name)
  await page.getByLabel('Phone').fill('050-123-4567')
  await page.getByLabel('Date of birth').fill('1990-01-15')
  await page.getByLabel('Gender').selectOption({ label: 'Prefer not to say' })
  if (withCar) {
    await page.getByLabel('I plan to offer rides, so add my car now').check()
    await page.getByLabel('Make').fill('Toyota')
    await page.getByLabel('Model').fill('Corolla')
    await page.getByLabel('Colour').fill('White')
    await page.getByLabel('Licence plate').fill('12-345-67')
  }
  await page.getByLabel(/I accept the RideMatch terms/).check()
  await page.getByRole('button', { name: 'Create profile' }).click()
}

async function newSession(browser: Browser, user: TestUser) {
  const context = await browser.newContext()
  const page = await context.newPage()
  await stubMapbox(page)
  await signInAs(page, user)
  return page
}

test.describe.configure({ mode: 'serial' })

test.describe('ride lifecycle', () => {
  let driver: TestUser
  let passenger: TestUser
  let driverPage: Page
  let passengerPage: Page
  let rideUrl = ''

  test.beforeAll(async ({ browser }) => {
    ;[driver, passenger] = await Promise.all([createTestUser('driver'), createTestUser('pass')])
    driverPage = await newSession(browser, driver)
    passengerPage = await newSession(browser, passenger)
  })

  test.afterAll(async () => {
    await driverPage?.context().close()
    await passengerPage?.context().close()
    await Promise.all([driver && deleteTestUser(driver), passenger && deleteTestUser(passenger)])
  })

  test('driver signs up and posts a ride', async () => {
    const page = driverPage
    await page.goto('/app')
    await onboard(page, driver, true)
    await page.getByRole('button', { name: /Offer seats/ }).click()
    await expect(page).toHaveURL(/\/app\/driver/)

    await page.goto('/app/driver/rides/new')
    await pickAddress(page, 'Pickup point', 'Dizengoff', FROM.address)
    await pickAddress(page, 'Destination', 'Azrieli', TO.address)
    await page.getByLabel('Departure').fill(localInputValue(new Date(Date.now() + 60 * 60_000)))
    await page.getByLabel('Price per seat').fill('25.00')
    await page.getByRole('button', { name: 'Post the ride' }).click()

    await expect(page).toHaveURL(/\/app\/driver\/rides\/\d+$/)
    rideUrl = new URL(page.url()).pathname
  })

  test('passenger finds the ride and asks for a seat', async () => {
    const page = passengerPage
    await page.goto('/app')
    await onboard(page, passenger, false)
    await page.getByRole('button', { name: /Find a ride/ }).click()
    await expect(page).toHaveURL(/\/app\/passenger/)

    await page.goto('/app/passenger/search')
    await pickAddress(page, 'Pickup point', 'Dizengoff', FROM.address)
    await pickAddress(page, 'Destination', 'Azrieli', TO.address)
    await page.getByLabel('Departure').fill(localInputValue(new Date(Date.now() + 60 * 60_000)))
    await page.getByRole('button', { name: 'Search' }).click()

    // The test DB can hold rides from earlier runs; open the one this run's driver posted.
    await page.getByRole('link', { name: new RegExp(driver.name) }).click()
    await page.getByRole('button', { name: 'Ask for a seat' }).click()
    await expect(page.getByText(/waiting|pending/i).first()).toBeVisible()
  })

  test('driver approves the request', async () => {
    const page = driverPage
    await page.goto('/app/driver/requests')
    await page.getByRole('button', { name: 'Approve' }).click()
    await expect(page.getByRole('button', { name: 'Approve' })).toHaveCount(0)
  })

  test('driver starts and finishes the ride', async () => {
    const page = driverPage
    await page.goto(rideUrl)
    await page.getByRole('button', { name: 'Start the ride' }).click()
    await page.getByRole('button', { name: 'Finish the ride' }).click()
    await expect(page.getByRole('button', { name: 'Finish the ride' })).toHaveCount(0)
  })

  test('passenger rates the driver', async () => {
    const page = passengerPage
    await page.goto('/app/passenger')
    await page.getByRole('link', { name: /Rate your ride/ }).click()
    await page.getByText('5', { exact: true }).click()
    await page.getByRole('button', { name: 'Send rating' }).click()

    await expect(page).toHaveURL(/\/app\/passenger$/)
    await expect(page.getByRole('link', { name: /Rate your ride/ })).toHaveCount(0)
  })
})
