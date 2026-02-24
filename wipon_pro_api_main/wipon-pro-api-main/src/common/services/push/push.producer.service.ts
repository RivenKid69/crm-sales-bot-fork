import { InjectQueue } from '@nestjs/bull';
import { Injectable } from '@nestjs/common';
import { Queue } from 'bull';

@Injectable()
export class PushProducerService {
  constructor(@InjectQueue('push_pro') private queue: Queue) {}

  async sendMessage(userId: number, pushToken: string, message, platform: string, unreadCount: number) {
    await this.queue.add('push_pro-job', { userId, message, pushToken, platform, unreadCount });
  }
}
