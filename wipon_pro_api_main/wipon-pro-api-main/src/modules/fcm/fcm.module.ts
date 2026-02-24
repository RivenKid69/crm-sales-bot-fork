import { forwardRef, Module } from '@nestjs/common';
import { ConfigService } from '@nestjs/config';
import { FcmService } from './fcm.service.';
import { NotificationsModule } from '../notifications/notifications.module';
import { PushProducerService } from '../../common/services/push/push.producer.service';
import { PushConsumer } from '../../common/services/consumer/push.consumer';
import { BullModule } from '@nestjs/bull';
import * as admin from 'firebase-admin';

@Module({
  providers: [ConfigService, FcmService, PushProducerService, PushConsumer],
  imports: [BullModule.registerQueue({ name: 'push_pro' }), forwardRef(() => NotificationsModule)],
  exports: [FcmService, PushProducerService, PushConsumer],
})
export class FcmModule {
  constructor(private readonly configService: ConfigService) {
    admin.initializeApp({
      credential: admin.credential.cert({
        projectId: this.configService.get<string>('FIREBASE_PROJECT_ID'),
        privateKey: this.configService.get<string>('FIREBASE_PRIVATE_KEY')?.replace(/\\n/g, '\n'),
        clientEmail: this.configService.get<string>('FIREBASE_CLIENT_EMAIL'),
      }),
    });
  }
}
