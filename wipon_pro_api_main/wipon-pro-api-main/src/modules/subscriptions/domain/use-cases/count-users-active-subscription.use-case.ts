import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SubscriptionRepository } from '../../data/subscription.repository';

@Injectable()
export class CountUsersActiveSubscriptionUseCase {
  constructor(
    @InjectRepository(SubscriptionRepository) private readonly subscriptionRepository: SubscriptionRepository,
  ) {}

  handle(userId: number): Promise<number> {
    return this.subscriptionRepository.count({ where: { user_id: userId, is_active: true } });
  }
}
