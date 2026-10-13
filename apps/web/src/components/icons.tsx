import type { SVGProps } from "react";

/** Small inline icon set (stroke icons, 1.75 weight) so the app ships no icon dependency. */
function Icon({ children, ...props }: SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" aria-hidden {...props}>{children}</svg>;
}

export const PlayIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M7 4.5v15l12-7.5-12-7.5Z" /></Icon>;
export const UploadIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 16V4m0 0-4 4m4-4 4 4M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" /></Icon>;
export const FilmIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M7 4v16M17 4v16M3 9h4M3 15h4M17 9h4M17 15h4" /></Icon>;
export const SparkIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" /></Icon>;
export const SendIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="m5 12 14-7-5 14-2.5-5.5L5 12Z" /></Icon>;
export const StopIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><rect x="6" y="6" width="12" height="12" rx="2" /></Icon>;
export const PlusIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 5v14M5 12h14" /></Icon>;
export const TerminalIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="m5 8 4 4-4 4M12 16h7" /></Icon>;
export const FileIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" /><path d="M14 3v5h5" /></Icon>;
export const BookIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2V5Z" /><path d="M4 19a2 2 0 0 0 2 2h13" /></Icon>;
export const CheckIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="m5 12 4.5 4.5L19 7" /></Icon>;
export const AlertIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 9v4M12 17h.01" /><path d="M10.3 3.9 2.6 17.5A2 2 0 0 0 4.3 20.5h15.4a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" /></Icon>;
export const LayersIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="m12 3 9 5-9 5-9-5 9-5Z" /><path d="m3 13 9 5 9-5" /></Icon>;
export const ChevronIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="m9 6 6 6-6 6" /></Icon>;
export const LogoutIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3" /></Icon>;
export const DownloadIcon = (props: SVGProps<SVGSVGElement>) => <Icon {...props}><path d="M12 4v12m0 0 4-4m-4 4-4-4M4 20h16" /></Icon>;
