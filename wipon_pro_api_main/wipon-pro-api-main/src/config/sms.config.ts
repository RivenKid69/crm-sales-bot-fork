export default {
  sendUrl: 'https://smsc.kz/sys/send.php',
  wipon: {
    sms_user: process.env.SMS_USERNAME || '',
    sms_password: process.env.SMS_PASSWORD || '',
  },
};
