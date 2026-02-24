import * as path from 'path';
import appConfig from './app.config';
const env = appConfig.environment;
const cyberplatOpenKey = ['staging', 'production'].includes(env) ? 'SSL_CYBERPLAT_OPEN' : 'SSL_WIPON_OPEN';

export const sslConfig = {
  cyberplat: {
    open: path.resolve('storage', 'app', 'ssl_keys', cyberplatOpenKey),
  },
};
