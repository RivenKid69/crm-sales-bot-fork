require('dotenv').config();

export default {
  environment: process.env.ENVIRONMENT || 'development',
  'api-key': process.env.API_KEY,
  smsToken: process.env.SMS_CALLBACK_TOKEN || '',
  transactionToken: process.env.TRANSACTION_TOKEN || '',

  wooppay: {
    login: process.env.WOOPPAY_LOGIN,
    password: process.env.WOOPPAY_PASSWORD,
    wsdl: process.env.WOOPPAY_WSDL || '',
  },
};
