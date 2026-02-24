import { CACHE_MANAGER, Inject, Injectable } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import { createCustomLogger } from '../../logger/request-logger';
import { getManager, IsNull, LessThan, Not } from 'typeorm';
import { SubscriptionDao } from '../../dao/subscription.dao';
import { DeviceDao } from '../../dao/device.dao';
import { getPrefixForDeletedDeviceCode, sleep } from '../../utils/common';
import { Cache } from 'cache-manager';
import { v4 as uuidv4 } from 'uuid';
import { DEACTIVATE_EXPIRED_SUBS_REDIS_KEY } from '../../../config/job.config';

@Injectable()
export class TasksService {
  @Inject(CACHE_MANAGER) private cacheManager: Cache;

  async generateUniqueKeyAndSetToRedis(saveKey: string) {
    const uuid = uuidv4();
    await this.cacheManager.set(saveKey, uuid, { ttl: 0 });
    await sleep(2);
    const savedUuid = await this.cacheManager.get(saveKey);
    return savedUuid == uuid;
  }

  @Cron('0 0 3 * * *', {
    name: 'deactivateExpiredSubscriptions',
    timeZone: 'Asia/Almaty',
  })
  async deactivateExpiredSubscriptions() {
    const canContinue = await this.generateUniqueKeyAndSetToRedis(DEACTIVATE_EXPIRED_SUBS_REDIS_KEY);
    if (!canContinue) return;
    try {
      const manager = getManager();
      await manager.update(
        SubscriptionDao,
        {
          is_active: true,
          expires_at: LessThan(new Date()),
        },
        {
          is_active: false,
          deleted_at: new Date(),
        },
      );

      const now = new Date();
      const yearAgo = new Date(now.setFullYear(now.getFullYear() - 1));
      const expiredDeviceCodes = await manager.find(DeviceDao, {
        where: { user_id: Not(IsNull()), updated_at: LessThan(yearAgo) },
      });

      expiredDeviceCodes.forEach((device) => {
        device.device_code = getPrefixForDeletedDeviceCode(device.user_id, device.device_code);
        device.updated_at = new Date();
        device.user_id = null;
      });

      await manager.save(expiredDeviceCodes);
    } catch (e) {
      const logger = createCustomLogger('info', 'deactivate-subscription-errors');
      logger.log('info', {
        message: 'While deactivate expired subscriptions task occurred error',
        e,
      });
    } finally {
      await this.cacheManager.del(DEACTIVATE_EXPIRED_SUBS_REDIS_KEY);
    }
  }
}
