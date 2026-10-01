import type { SVGProps } from 'react'

type IconProps = SVGProps<SVGSVGElement>

function Icon({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      {...props}
    >
      {children}
    </svg>
  )
}

export const BoardIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 6h16M4 12h10M4 18h13" />
  </Icon>
)

export const WheelIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="2.6" />
    <path d="M12 3.5v6M3.8 13.4l5.6-1.9M20.2 13.4l-5.6-1.9" />
  </Icon>
)

export const SeatIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M8 4h3a3 3 0 0 1 3 3v7H8z" />
    <path d="M8 14h9a3 3 0 0 1 3 3v3" />
    <path d="M5 20v-7" />
  </Icon>
)

export const SearchIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="11" cy="11" r="6.5" />
    <path d="m16 16 4.5 4.5" />
  </Icon>
)

export const InboxIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M4 13V6a2 2 0 0 1 2-2h12a2 2 0 0 1 2 2v7" />
    <path d="M4 13h4l1.5 3h5L16 13h4v5a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2z" />
  </Icon>
)

export const BellIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="M6 10a6 6 0 1 1 12 0c0 4 1.3 5.3 1.9 6H4.1C4.7 15.3 6 14 6 10" />
    <path d="M10 20a2 2 0 0 0 4 0" />
  </Icon>
)

export const PersonIcon = (props: IconProps) => (
  <Icon {...props}>
    <circle cx="12" cy="8.5" r="3.8" />
    <path d="M4.8 20a7.4 7.4 0 0 1 14.4 0" />
  </Icon>
)

export const CheckIcon = (props: IconProps) => (
  <Icon {...props}>
    <path d="m4.5 12.5 5 5 10-11" />
  </Icon>
)
