import { createLogger, format, transports } from 'winston';
import { getNowAlmatyTime } from '../helpers/datetime';

const createCustomErrorLogger = () => {
  const date = getNowAlmatyTime().toLocaleDateString('kk-KK').split('/').join('.');
  const options = {
    level: 'error',
    format: format.combine(
      format.timestamp({
        format: 'YYYY-MM-DD HH:mm:ss',
      }),
      format.json(),
    ),
    transports: [new transports.File({ filename: `dist/static/logs/errors-${date}.log` })],
  };

  const errorLogger = createLogger(options);

  if (process.env.NODE_ENV !== 'production') {
    errorLogger.add(
      new transports.Console({
        format: format.combine(format.colorize(), format.simple()),
      }),
    );
  }

  return errorLogger;
};

export default createCustomErrorLogger;
