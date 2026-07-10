import versionData from "../../../version.json";

export type AppVersion = {
  major: number;
  minor: number;
  build: number;
  tagline?: string;
};

export const APP_VERSION = versionData as AppVersion;

export function formatAppVersionLabel(v: AppVersion = APP_VERSION): string {
  return `V${v.major}.${v.minor}-Build ${v.build}`;
}

export const APP_TAGLINE = APP_VERSION.tagline ?? "Quality Engineering OS";
