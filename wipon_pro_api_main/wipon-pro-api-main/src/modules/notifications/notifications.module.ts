import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { NotificationsRepository } from './data/notifications.repository';
import { NotificationsController } from './presenter/notifications.controller';
import { NotificationsService } from './domain/notifications.service';
import { UsersModule } from '../users/users.module';
import { PushService } from '../../common/services/push/push.service';
import { FcmModule } from '../fcm/fcm.module';

@Module({
  imports: [TypeOrmModule.forFeature([NotificationsRepository]), UsersModule, FcmModule],
  providers: [NotificationsService, PushService],
  controllers: [NotificationsController],
  exports: [NotificationsService],
})
export class NotificationsModule {}
