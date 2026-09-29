import { useMe } from "../api/queries";

const DEVICE_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

/** The time zone of the user's city: "today" in the app is always the city's today. */
export function useCityZone(): string {
  return useMe().data?.city.timezone ?? DEVICE_ZONE;
}
