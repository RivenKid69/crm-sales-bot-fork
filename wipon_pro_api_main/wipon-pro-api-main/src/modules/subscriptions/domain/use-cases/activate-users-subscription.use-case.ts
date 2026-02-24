import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { SubscriptionRepository } from '../../data/subscription.repository';
import { EntityManager } from 'typeorm';
import { SubscriptionDao } from '../../../../common/dao/subscription.dao';
import { addDays, getNowAlmatyTime } from '../../../../common/helpers/datetime';
import subscriptionConfig from '../../../../config/subscription.config';
import { PushService } from '../../../../common/services/push/push.service';
import { I18nRequestScopeService } from 'nestjs-i18n';
import { UserDao } from '../../../../common/dao/user.dao';

@Injectable()
export class ActivateUsersSubscriptionUseCase {
  constructor(
    @InjectRepository(SubscriptionRepository) private readonly subscriptionRepository: SubscriptionRepository,
    private readonly pushService: PushService,
    private readonly i18n: I18nRequestScopeService,
  ) {}

  async handle(user: UserDao, days: number, transaction: null | EntityManager = null): Promise<boolean> {
    const activeSubsCount = await this.subscriptionRepository.count({ where: { user_id: user.id, is_active: true } });
    const isPush = !activeSubsCount;

    if (!transaction) {
      await this.subscriptionRepository.update({ user_id: user.id }, { is_active: false });
    } else {
      await transaction.update(SubscriptionDao, { user_id: user.id }, { is_active: false });
    }

    const expiresAt = addDays(new Date(), days);
    let type: string | null;
    switch (days) {
      case subscriptionConfig.lifetime:
        type = subscriptionConfig.type;
        break;
      case subscriptionConfig.quarter_lifetime:
        type = subscriptionConfig.quarter_type;
        break;
      case subscriptionConfig.monthly_lifetime:
        type = subscriptionConfig.monthly_type;
        break;
      default:
        type = null;
    }

    const subscription = this.subscriptionRepository.create({
      user_id: user.id,
      is_active: true,
      expires_at: expiresAt,
      type,
      created_at: new Date(),
      updated_at: new Date(),
    });

    if (!transaction) {
      await this.subscriptionRepository.save(subscription);
    } else {
      await transaction.save(subscription);
    }

    if (isPush) {
      let cost: number;
      days == subscriptionConfig.quarter_lifetime
        ? (cost = subscriptionConfig.quarter_cost)
        : (cost = subscriptionConfig.cost);
      const message = await this.i18n.translate('messages.subscription_activated', {
        args: {
          cost: cost,
          new_start_at: subscription.created_at.toLocaleDateString('kk-KK'),
          new_expires_at: subscription.expires_at.toLocaleDateString('kk-KK'),
        },
      });
      await this.pushService.send(user, message);
    }

    return true;
  }
}
