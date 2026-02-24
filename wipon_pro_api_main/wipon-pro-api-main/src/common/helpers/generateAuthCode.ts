import appConfig from '../../config/app.config';
const env = appConfig.environment;

function getRandomIntInclusive(min: number, max: number): number {
  min = Math.ceil(min);
  max = Math.floor(max);
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

export default function () {
  if (env === 'production') {
    return String(getRandomIntInclusive(0, Math.pow(10, 6) - 1)).padStart(6, '1');
  }
  return '123456';
}
