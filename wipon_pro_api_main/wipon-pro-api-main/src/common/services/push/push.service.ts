import { Injectable } from '@nestjs/common';
import { NotificationDao } from '../../dao/notification.dao';
import appConfig from '../../../config/app.config';
import { UserDao } from '../../dao/user.dao';
import { PushProducerService } from './push.producer.service';

@Injectable()
export class PushService {
  constructor(private readonly pushProducerService: PushProducerService) {}
  async send(user: UserDao | undefined, message: string) {
    if (!user || !user.device) return false;
    let platform = user.device?.platform;

    if (!platform) return false;

    if (platform.includes('Android')) platform = 'Android';
    else if (platform.includes('iOS')) platform = 'iOS';
    else return true;

    const pushToken = user.device?.push_token;
    if (!pushToken) return false;

    let unreadCount = await NotificationDao.count({ where: { user_id: user.id, is_unread: true } });
    unreadCount += 1;

    const env = appConfig.environment;

    await this.pushProducerService.sendMessage(user.id, pushToken, message, platform, unreadCount);
    return true;
  }
}
