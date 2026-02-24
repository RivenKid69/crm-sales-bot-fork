import { CACHE_MANAGER, Inject, Injectable } from '@nestjs/common';
import { sleep } from '../../utils/common';
import { v4 as uuidv4 } from 'uuid';
import { Cache } from 'cache-manager';
import { Cron } from '@nestjs/schedule';
import { LINK_STORE_TO_LICENSE_KEY } from '../../../config/job.config';
import { createCustomLogger } from '../../logger/request-logger';
import { getManager } from 'typeorm';
import { StoreDao } from '../../dao/store.dao';

@Injectable()
export class LinkStoreToLicenseTask {
  constructor(@Inject(CACHE_MANAGER) private cacheManager: Cache) {}

  async generateUniqueKeyAndSetToRedis(saveKey: string) {
    const uuid = uuidv4();
    await this.cacheManager.set(saveKey, uuid, { ttl: 0 });
    await sleep(2);
    const savedUuid = await this.cacheManager.get(saveKey);
    return savedUuid == uuid;
  }

  @Cron('0 0 5 * * *', {
    name: 'LinkStoreToLicenseTask',
    timeZone: 'Asia/Almaty',
  })
  async linkStoreToLicenseTask() {
    const canContinue = await this.generateUniqueKeyAndSetToRedis(LINK_STORE_TO_LICENSE_KEY);
    if (!canContinue) return;
    try {
      const manager = getManager();
      const result = (await manager.query(
        'SELECT ugd_licenses.id as license_id, stores.id as store_id from ugd_licenses ' +
          'inner join stores on ugd_licenses.bin = stores.buisness_bin ' +
          'where status = $1 and stores.ugd_license_id is null and ' +
          'stores.buisness_ugd_id = ugd_licenses.ugds_id and ' +
          'stores.buisness_dgd_id = ugd_licenses.dgds_id and ' +
          'stores.license_number = ugd_licenses.license_number',
        ['Действительный'],
      )) as Array<{ license_id: number; store_id: number }>;

      if (result.length) {
        for (const data of result) {
          await manager.update(StoreDao, data.store_id, { ugd_license_id: data.license_id });
        }
      }
    } catch (e) {
      const logger = createCustomLogger('info', 'link-store-to-license-errors');
      logger.log('info', {
        message: 'While linking store to license task occurred error',
        e,
      });
    } finally {
      await this.cacheManager.del(LINK_STORE_TO_LICENSE_KEY);
    }
  }
}
