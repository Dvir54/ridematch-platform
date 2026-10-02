import { Navigate, Route, Routes } from 'react-router-dom'
import { ApiTokenBridge } from './auth/ApiTokenBridge'
import { useCurrentUser } from './auth/currentUserContext'
import { RequireMode, RequireProfile, RequireSignedIn } from './auth/guards'
import { AppShell } from './components/AppShell'
import { ButtonLink } from './components/Button'
import { MessageScreen } from './components/states'
import { SignInScreen, SignUpScreen } from './features/auth/AuthScreens'
import { CreateRideScreen } from './features/driver/CreateRideScreen'
import { DriverHomeScreen } from './features/driver/DriverHomeScreen'
import { DriverRideScreen } from './features/driver/DriverRideScreen'
import { EditRideScreen } from './features/driver/EditRideScreen'
import { IncomingRequestsScreen } from './features/driver/IncomingRequestsScreen'
import { MyRidesScreen } from './features/driver/MyRidesScreen'
import { NotificationsScreen } from './features/notifications/NotificationsScreen'
import { OnboardingScreen } from './features/onboarding/OnboardingScreen'
import { RoleSelectionScreen } from './features/onboarding/RoleSelectionScreen'
import { MyTripsScreen } from './features/passenger/MyTripsScreen'
import { PassengerHomeScreen } from './features/passenger/PassengerHomeScreen'
import { PassengerRideScreen } from './features/passenger/PassengerRideScreen'
import { SearchScreen } from './features/passenger/SearchScreen'
import { ProfileScreen } from './features/profile/ProfileScreen'
import { PublicProfileScreen } from './features/profile/PublicProfileScreen'
import { RateScreen } from './features/ratings/RateScreen'
import { WelcomeScreen } from './features/welcome/WelcomeScreen'
import { homePathFor, paths } from './routes'

/** `/app` itself has no screen; it opens whichever mode the user last chose. */
function HomeRedirect() {
  const user = useCurrentUser()
  return <Navigate to={homePathFor(user.preferences.default_mode ?? 'passenger')} replace />
}

function NotFoundScreen() {
  return (
    <MessageScreen
      title="No such page"
      body="The link may be out of date, or the ride it pointed at is gone."
      action={<ButtonLink to={paths.welcome}>Back to the start</ButtonLink>}
    />
  )
}

export function App() {
  return (
    <>
      <ApiTokenBridge />
      <Routes>
        <Route path={paths.welcome} element={<WelcomeScreen />} />
        <Route path="/sign-in/*" element={<SignInScreen />} />
        <Route path="/sign-up/*" element={<SignUpScreen />} />

        <Route element={<RequireSignedIn />}>
          <Route path={paths.onboarding} element={<OnboardingScreen />} />

          <Route element={<RequireProfile />}>
            <Route path={paths.role} element={<RoleSelectionScreen />} />

            <Route element={<RequireMode />}>
              <Route path={paths.app} element={<AppShell />}>
                <Route index element={<HomeRedirect />} />

                <Route path="driver" element={<DriverHomeScreen />} />
                <Route path="driver/rides" element={<MyRidesScreen />} />
                <Route path="driver/rides/new" element={<CreateRideScreen />} />
                <Route path="driver/rides/:rideId" element={<DriverRideScreen />} />
                <Route path="driver/rides/:rideId/edit" element={<EditRideScreen />} />
                <Route path="driver/requests" element={<IncomingRequestsScreen />} />

                <Route path="passenger" element={<PassengerHomeScreen />} />
                <Route path="passenger/search" element={<SearchScreen />} />
                <Route path="passenger/trips" element={<MyTripsScreen />} />
                <Route path="passenger/rides/:rideId" element={<PassengerRideScreen />} />

                <Route path="notifications" element={<NotificationsScreen />} />
                <Route path="profile" element={<ProfileScreen />} />
                <Route path="users/:userId" element={<PublicProfileScreen />} />
                <Route path="rate/:rideId/:userId" element={<RateScreen />} />
              </Route>
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<NotFoundScreen />} />
      </Routes>
    </>
  )
}
