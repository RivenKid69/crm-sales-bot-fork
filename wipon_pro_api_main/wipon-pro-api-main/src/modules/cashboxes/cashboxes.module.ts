import { Module } from '@nestjs/common';
import { CashboxesService } from './domain/cashboxes.service';
import { PushService } from '../../common/services/push/push.service';
import { CashboxesController } from './presenter/cashboxes.controller';
import { UsersModule } from '../users/users.module';
import { FcmModule } from '../fcm/fcm.module';

@Module({
  providers: [CashboxesService, PushService],
  controllers: [CashboxesController],
  imports: [UsersModule, FcmModule],
})
export class CashboxesModule {}
