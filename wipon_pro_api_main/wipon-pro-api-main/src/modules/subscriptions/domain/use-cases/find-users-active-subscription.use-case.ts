import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SubscriptionRepository } from '../../data/subscription.repository';
import { SubscriptionDao } from '../../../../common/dao/subscription.dao';

@Injectable()
export class FindUsersActiveSubscriptionUseCase {
  constructor(
    @InjectRepository(SubscriptionRepository) private readonly subscriptionRepository: SubscriptionRepository,
  ) {}

  handle(userId: number): Promise<SubscriptionDao | undefined> {
    return this.subscriptionRepository.findOne({ where: { user_id: userId, is_active: true, deleted_at: null } });
  }
}
