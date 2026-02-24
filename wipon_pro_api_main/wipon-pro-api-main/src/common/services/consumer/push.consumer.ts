import { Process, Processor } from '@nestjs/bull';
import { Job } from 'bull';
import { PushJobType } from '../../types/push-job.type';
import { MessagingPayload } from 'firebase-admin/lib/messaging/messaging-api';
import { NotificationsService } from '../../../modules/notifications/domain/notifications.service';
import { FcmService } from '../../../modules/fcm/fcm.service.';
import { createCustomLogger } from '../../logger/request-logger';

@Processor('push_pro')
export class PushConsumer {
  constructor(private readonly notificationsService: NotificationsService, private readonly fcmService: FcmService) {}
  @Process('push_pro-job')
  async readOperationJob(job: Job<PushJobType>) {
    const logger = createCustomLogger('info', 'notifications');
    const TOKEN = job.data.pushToken;
    const PLATFORM = job.data.platform;
    const USERID = job.data.userId;
    const MESSAGE = job.data.message;

    try {
      const result = await this.notificationsService.createUsersNotification(USERID, MESSAGE);
      const sendMessage: MessagingPayload = {
        notification: {
          body: MESSAGE,
          title: 'Wipon pro',
          badge: String(job.data.unreadCount),
        },
        data: {
          id: String(result.id),
          click_action: 'FLUTTER_NOTIFICATION_CLICK',
        },
      };
      await this.fcmService.sendNotification(TOKEN, sendMessage);
    } catch (error) {
      logger.log('error', { message: `Can't send PUSH notification to ${PLATFORM} ${TOKEN}`, error });
    }

    logger.log('info', { message: `PUSH notification sent to ${PLATFORM} ${TOKEN}` });
  }
}
