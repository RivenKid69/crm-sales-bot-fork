import { Injectable } from '@nestjs/common';
import smsConfig from '../../config/sms.config';
import createCustomErrorLogger from '../../common/logger/error-logger';
const FormData = require('form-data');
import appConfig from '../../config/app.config';

@Injectable()
export class SmsService {
  async sendAuthCode(phoneNumber: string, authCode: string): Promise<boolean> {
    try {
      if (appConfig.environment != 'production') return true;
      const response = await this.sendSms(phoneNumber, authCode);
      return response?.cnt == 1;
    } catch (e) {
      const errorResponse = e.response || e?.toJSON;
      if (errorResponse) {
        const errorLogger = createCustomErrorLogger();
        errorLogger.log('error', {
          message: "Can't send SMS message!",
          response: {
            body: errorResponse.message || 'no response',
            statusCode: errorResponse ? errorResponse.code : 'unknown',
          },
        });
      }
      return false;
    }
  }

  sendSms(phone: string, authCode: string): any {
    const fd = new FormData();
    fd.append('fmt', 3);
    fd.append('login', smsConfig.wipon.sms_user);
    fd.append('psw', smsConfig.wipon.sms_password);
    fd.append('phones', phone);
    fd.append('mes', `СМС-код для авторизации в Wipon: ${authCode}`);
    fd.append('sender', 'Wipon Pro');
    fd.append('charset', 'utf-8');

    return new Promise((resolve, reject) => {
      fd.submit(smsConfig.sendUrl, function (err, res) {
        if (err) {
          reject(err);
        }
        res.setEncoding('utf-8');
        let full_data = '';

        res.on('data', function (data) {
          full_data += data;
        });

        res.on('end', function (data) {
          resolve(JSON.parse(full_data));
        });
      });
    });
  }
}
