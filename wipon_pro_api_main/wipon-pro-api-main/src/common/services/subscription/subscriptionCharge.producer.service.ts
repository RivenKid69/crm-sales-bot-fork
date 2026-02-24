import { InjectQueue } from '@nestjs/bull';
import { Injectable } from '@nestjs/common';
import { Queue } from 'bull';

@Injectable()
export class SubscriptionChargeProducerService {
  constructor(@InjectQueue('billing_pro') private queue: Queue) {}

  async sendBilling(userId: number) {
    await this.queue.add('billing_pro-job', { userId }, { delay: 300000 });
  }
}
