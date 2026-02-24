import { SubscriptionDao } from '../../../common/dao/subscription.dao';
import { EntityRepository, Repository, UpdateResult } from 'typeorm';

@EntityRepository(SubscriptionDao)
export class SubscriptionRepository extends Repository<SubscriptionDao> {
  async findUsersSubscription(userId: number): Promise<SubscriptionDao | null> {
    const subscription = await this.findOne({ order: { created_at: 'DESC' }, where: { user_id: userId } });
    if (!subscription) return null;
    return subscription;
  }

  async deactivateSubscription(subscription: SubscriptionDao): Promise<UpdateResult> {
    return await this.update(subscription.id, {
      is_active: false,
      deleted_at: new Date(),
    });
  }
}
