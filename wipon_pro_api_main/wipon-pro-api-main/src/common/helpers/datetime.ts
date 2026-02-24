const oneMinute = 60000;
const oneHour = 60 * oneMinute;
const oneDay = 24 * oneHour;

export const greaterThan = (valueDate: Date, comparingDate: Date): boolean => {
  return valueDate.valueOf() > comparingDate.valueOf();
};

export const gtNow = (time: Date): boolean => {
  return Date.now() < time.valueOf();
};

export const ltNow = (time: Date): boolean => {
  return Date.now() > time.valueOf();
};

export const addSeconds = (time: Date, seconds: number): Date => {
  const timestamp = time.valueOf() + seconds * 1000;
  return new Date(timestamp);
};

export const diffInSecondsFromNow = (time: Date): number => {
  return Math.abs(Math.round((time.valueOf() - Date.now()) / 1000));
};
export const diffInMinutesFromNow = (time: Date): number => {
  return Math.abs(Math.round((time.valueOf() - Date.now()) / oneMinute));
};

export const addMinutesFromNow = (minutes: number): Date => {
  const ts = Date.now() + minutes * oneMinute;
  return new Date(ts);
};

export const subMinutesFromNow = (minutes: number) => {
  const ts = Date.now() - minutes * oneMinute;
  return new Date(ts);
};

// export const convertTZ = (date: Date, timezone: string): string => {
//   return date.toLocaleString('en-US', { timeZone: timezone })
// };

export const getStartOfMonth = (date): Date => {
  const start = new Date(date.getFullYear(), date.getMonth(), 1);
  return new Date(start.valueOf());
};

export const addDays = (date: Date, days: number) => {
  return new Date(date.valueOf() + days * oneDay);
};

export const getNowAlmatyTime = (ts: null | number = null) => {
  const d = ts ? ts : Date.now();
  return new Date(d + 6 * oneHour);
};

export const getDiffInSecsTillTomorrow = () => {
  const date = new Date();
  date.setDate(date.getDate() + 1);
  date.setHours(0, 0, 0);
  return Math.round((date.valueOf() - Date.now()) / 1000);
};
