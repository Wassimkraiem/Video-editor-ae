import type { HTMLAttributes } from "react";

declare module "react" {
  namespace JSX {
    interface IntrinsicElements {
      "hyperframes-player": HTMLAttributes<HTMLElement> & { src?: string; controls?: boolean };
    }
  }
}
