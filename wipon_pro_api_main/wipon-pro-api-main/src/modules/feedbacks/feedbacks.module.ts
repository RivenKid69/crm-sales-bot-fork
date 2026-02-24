import { Module } from '@nestjs/common';
import { FeedbacksController } from './presenter/feedbacks.controller';
import { FeedbacksService } from './domain/feedbacks.service';
import { TypeOrmModule } from '@nestjs/typeorm';
import { FeedbacksRepository } from './data/feedbacks.repository';
import { DoomguyService } from '../../common/services/doomguy/doomguy.service';
import { HttpModule } from '@nestjs/axios';
import { UsersModule } from '../users/users.module';

@Module({
  imports: [TypeOrmModule.forFeature([FeedbacksRepository]), HttpModule, UsersModule],
  providers: [FeedbacksService, DoomguyService],
  controllers: [FeedbacksController],
})
export class FeedbacksModule {}
