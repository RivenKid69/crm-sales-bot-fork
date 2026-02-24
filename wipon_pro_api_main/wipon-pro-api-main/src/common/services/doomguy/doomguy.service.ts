import { Injectable } from '@nestjs/common';
import { HttpService } from '@nestjs/axios';
import createCustomErrorLogger from '../../logger/error-logger';
import appConfig from '../../../config/app.config';
import { getNowAlmatyTime } from '../../helpers/datetime';
import { PostCallbackDto } from '../../../modules/sms/dto/post-callback.dto';

@Injectable()
export class DoomguyService {
  private _hookUrl = process.env.WIPON_DOOMGUY_WEBHOOK_URL || '';

  constructor(private readonly httpService: HttpService) {}

  private async executeCurl(postFields): Promise<boolean> {
    try {
      const response = await this.httpService.axiosRef.post(this._hookUrl, postFields);
      return response.status == 200;
    } catch (e) {
      const errorResponse = e.response;
      const responseStatus = errorResponse ? errorResponse.status : 'Недоступен';
      const responseBody = errorResponse ? errorResponse.data : 'no response';
      const errorLogger = createCustomErrorLogger();
      errorLogger.log('error', {
        message: postFields,
        slackResponse: {
          statusCode: responseStatus,
          body: responseBody,
        },
      });
      return false;
    }
  }

  async sendFeedback(messageFields): Promise<boolean> {
    return this.executeCurl({
      channel: appConfig.environment == 'production' ? '#feedback' : '#doomguy',
      username: 'Doomguy PRO™',
      text: `Пользователь отправил вам следующее сообщение из приложения Wipon Pro: 
      *Текст:*: \`\`\`${messageFields.text}\`\`\`.
      *Отправлено:*: ${messageFields.date}.
      *Имя пользователя:* ${messageFields.name}.
      *Электронная почта пользователя:* ${messageFields.email}.
      *Телефон пользователя:* ${messageFields.phone_number}.
      *ID пользователя:* ${messageFields.user_id}
      *Версия приложения:* ${messageFields.app_version}
      *Модель и платформа телефона:* ${messageFields.platform}
      *Ключ PUSH уведомления:* ${messageFields.push_token}`,
      icon_emoji: ':godmode:',
    });
  }

  sendSmsCallback(postCbDto: PostCallbackDto) {
    return this.executeCurl({
      channel: appConfig.environment == 'staging' ? '#smsc' : '#doomguy',
      username: 'Doomguy PRO™',
      text: `*Отчёт по отправке SMS:
      *ID сообщения:* ${postCbDto.id}.
      *Номер телефона:* ${postCbDto.phone}.
      *Время:* ${postCbDto.time}. 
      *Статус:* ${postCbDto.status}. 
      *Код ошибки:* ${postCbDto.err || '0'}
      `,
    });
  }

  async commitRage(reason: string, message: string, channel: string | null = null): Promise<boolean> {
    const date = getNowAlmatyTime();
    return this.executeCurl({
      channel: appConfig.environment == 'production' ? (channel ? channel : '#alert') : '#doomguy',
      username: 'Doomguy PRO™',
      text: `*ВНИМАНИЕ!* Doomguy в ярости!. 
      *Причина ярости*: ${reason}.
      *Сообщение исключения*: ${message}.
      *Время фиксации ярости*: ${date.toLocaleDateString('ru-RU', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })}`,
      icon_emoji: ':godmode:',
    });
  }
}
