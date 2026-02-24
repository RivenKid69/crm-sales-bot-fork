import { Module } from '@nestjs/common';
import { SmsService } from './sms.service';
import { HttpModule } from '@nestjs/axios';
import { SmsController } from './presenter/sms.controller';
import { SmscService } from './domain/smsc.service';
import { DoomguyService } from '../../common/services/doomguy/doomguy.service';

@Module({
  imports: [HttpModule],
  providers: [SmsService, SmscService, DoomguyService],
  controllers: [SmsController],
  exports: [SmsService],
})
export class SmsModule {}
