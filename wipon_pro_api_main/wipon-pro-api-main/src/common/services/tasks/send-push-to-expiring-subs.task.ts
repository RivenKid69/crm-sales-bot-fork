import { CACHE_MANAGER, Inject, Injectable } from '@nestjs/common';
import { sleep } from '../../utils/common';
import { v4 as uuidv4 } from 'uuid';
import { Cache } from 'cache-manager';
import { Cron } from '@nestjs/schedule';
import { PUSH_TO_EXPIRING_SUBS_KEY } from '../../../config/job.config';
import { createCustomLogger } from '../../logger/request-logger';
import { DateTime } from 'luxon';
import { getManager } from 'typeorm';
import { SubscriptionDao } from '../../dao/subscription.dao';
import { UserDao } from '../../dao/user.dao';
import { expiringSubPushNotificationText } from '../../../config/subscription.config';
import { PushService } from '../push/push.service';
import { FindUserByIdUseCase } from '../../../modules/users/domain/use-cases/find-user-by-id.use-case';

@Injectable()
export class SendPushToExpiringSubsTask {
  constructor(
    private readonly pushService: PushService,
    private readonly findUserById: FindUserByIdUseCase,
    @Inject(CACHE_MANAGER) private cacheManager: Cache,
  ) {}

  async generateUniqueKeyAndSetToRedis(saveKey: string) {
    const uuid = uuidv4();
    await this.cacheManager.set(saveKey, uuid, { ttl: 0 });
    await sleep(2);
    const savedUuid = await this.cacheManager.get(saveKey);
    return savedUuid == uuid;
  }

  @Cron('0 0 9 * * *', {
    name: 'sendPushNotificationsToExpiringSubs',
    timeZone: 'Asia/Almaty',
  })
  async sendPushNotificationsToExpiringSubs() {
    const canContinue = await this.generateUniqueKeyAndSetToRedis(PUSH_TO_EXPIRING_SUBS_KEY);
    if (!canContinue) return;
    try {
      const date = DateTime.local().setZone('Asia/Almaty').plus({ day: 2 }).toSQLDate();

      const manager = getManager();
      const subQuery = await manager
        .createQueryBuilder(SubscriptionDao, 'subs')
        .select('MAX("subs".id)', 'id')
        .addSelect('"subs".user_id', 'user_id')
        .groupBy('"subs".user_id');

      const ids = await manager
        .createQueryBuilder(UserDao, 'users')
        .select('"users".id')
        .innerJoin('(' + subQuery.getQuery() + ')', 'subscription_data', '"subscription_data".user_id = "users".id')
        .leftJoin('subscriptions', 'subscriptions', '"subscription_data".id = "subscriptions".id')
        .where("subscriptions.is_active = true and subscriptions.type != 'Nurkassa'")
        .andWhere('subscriptions.expires_at < :date', { date })
        .getRawMany();

      const userIds = ids.map((el) => el.id);

      for (const userId of userIds) {
        const user = await this.findUserById.handle(userId);
        await this.pushService.send(user, expiringSubPushNotificationText);
      }
    } catch (e) {
      const logger = createCustomLogger('info', 'send-push-to-expiring-subs-errors');
      logger.log('info', {
        message: 'While sending push notifications to expiring subs task occurred error',
        e,
      });
    } finally {
      await this.cacheManager.del(PUSH_TO_EXPIRING_SUBS_KEY);
    }
  }
}
