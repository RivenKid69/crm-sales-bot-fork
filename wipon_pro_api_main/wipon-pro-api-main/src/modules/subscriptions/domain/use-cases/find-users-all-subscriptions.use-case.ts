import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SubscriptionRepository } from '../../data/subscription.repository';
import { SubscriptionDao } from '../../../../common/dao/subscription.dao';

@Injectable()
export class FindUsersAllSubscriptionsUseCase {
  constructor(
    @InjectRepository(SubscriptionRepository) private readonly subscriptionRepository: SubscriptionRepository,
  ) {}

  handle(userId: number): Promise<SubscriptionDao[]> {
    return this.subscriptionRepository.find({ where: { user_id: userId } });
  }
}
