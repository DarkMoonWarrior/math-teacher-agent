import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconBase({ children, ...props }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      fill="none"
      height="20"
      viewBox="0 0 24 24"
      width="20"
      {...props}
    >
      {children}
    </svg>
  );
}

export function SearchIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="11" cy="11" r="6.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="m16 16 4 4" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function FormulaIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4.5 7h3l2 10 3-12h7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="M14 11h5M16.5 8.5v5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function ShieldIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3 19 6v5c0 4.6-2.8 8.1-7 10-4.2-1.9-7-5.4-7-10V6l7-3Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="m9 12 2 2 4-4" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function BookIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5 4.5h10.5A2.5 2.5 0 0 1 18 7v12H7.5A2.5 2.5 0 0 1 5 16.5v-12Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="M5 16.5A2.5 2.5 0 0 1 7.5 14H18M9 8h5" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function PaperIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M7 3.5h8l3 3V20H7V3.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="M15 3.5V7h3M10 11h5M10 14.5h5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function LibraryIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5 5.5h5l1.5 2H19V19H5V5.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="M5 9h14M9 13h6" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function UploadIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
      <path d="M5 14.5V20h14v-5.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function CameraIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 8.5h3l1.4-2h7.2l1.4 2h3v10H4v-10Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.6" />
      <circle cx="12" cy="13.5" r="3.2" stroke="currentColor" strokeWidth="1.6" />
    </IconBase>
  );
}

export function CropIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M7 3v14h14M3 7h14v14" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function RotateIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5 8V4m0 0h4M5 4l3 3a7 7 0 1 1-2 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function ImageIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect height="15" rx="1.5" stroke="currentColor" strokeWidth="1.6" width="18" x="3" y="4.5" />
      <circle cx="8.5" cy="9" r="1.5" stroke="currentColor" strokeWidth="1.4" />
      <path d="m5 17 4.2-4 2.8 2.5 2.6-3 4.4 4.5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function LockIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <rect height="10" rx="1.5" stroke="currentColor" strokeWidth="1.6" width="14" x="5" y="10" />
      <path d="M8 10V7.5a4 4 0 0 1 8 0V10M12 14v2" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function ClockIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12 7v5l3 2" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function ArrowUpIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 19V5m0 0-5 5m5-5 5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </IconBase>
  );
}

export function CloseIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m7 7 10 10M17 7 7 17" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
    </IconBase>
  );
}

export function CheckIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="m5 12 4.5 4.5L19 7" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
    </IconBase>
  );
}

export function ArrowLeftIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M19 12H5m0 0 5-5m-5 5 5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </IconBase>
  );
}

export function ArrowRightIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M5 12h14m0 0-5-5m5 5-5 5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </IconBase>
  );
}

export function HistoryIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M4 6v5h5" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.6" />
      <path d="M5.2 15.8A8 8 0 1 0 4.3 9" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
      <path d="M12 7.5V12l3 1.8" stroke="currentColor" strokeLinecap="round" strokeWidth="1.6" />
    </IconBase>
  );
}

export function PlusIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 5v14M5 12h14" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
    </IconBase>
  );
}

export function SparkIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M12 3.5c.55 3.73 2.78 5.96 6.5 6.5-3.72.55-5.95 2.78-6.5 6.5-.55-3.72-2.78-5.95-6.5-6.5 3.72-.54 5.95-2.77 6.5-6.5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.5" />
      <path d="M18.2 16.2c.2 1.3 1 2.1 2.3 2.3-1.3.2-2.1 1-2.3 2.3-.2-1.3-1-2.1-2.3-2.3 1.3-.2 2.1-1 2.3-2.3Z" fill="currentColor" />
    </IconBase>
  );
}

export function SettingsIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M19 12a7 7 0 0 0-.1-1.2l2-1.5-2-3.4-2.4 1a8 8 0 0 0-2-1.2L14.2 3h-4.4l-.3 2.7a8 8 0 0 0-2 1.2l-2.4-1-2 3.4 2 1.5A7 7 0 0 0 5 12c0 .4 0 .8.1 1.2l-2 1.5 2 3.4 2.4-1a8 8 0 0 0 2 1.2l.3 2.7h4.4l.3-2.7a8 8 0 0 0 2-1.2l2.4 1 2-3.4-2-1.5c.1-.4.1-.8.1-1.2Z" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.45" />
    </IconBase>
  );
}

export function SignOutIcon(props: IconProps) {
  return (
    <IconBase {...props}>
      <path d="M10 5H5v14h5M14 8l4 4-4 4M8 12h10" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
    </IconBase>
  );
}
