import { createLogger, format, transports } from 'winston';
import { getNowAlmatyTime } from '../helpers/datetime';

export const createCustomLogger = (level, filename) => {
  const date = getNowAlmatyTime().toLocaleDateString('kk-KK').split('/').join('.');

  const logger = createLogger({
    level,
    format: format.combine(
      format.timestamp({
        format: 'YYYY-MM-DD HH:mm:ss',
      }),
      format.json(),
    ),
    transports: [new transports.File({ filename: `dist/static/logs/${filename}-${date}.log` })],
  });

  if (process.env.NODE_ENV !== 'production') {
    logger.add(
      new transports.Console({
        format: format.combine(format.colorize(), format.simple()),
      }),
    );
  }

  return logger;
};
