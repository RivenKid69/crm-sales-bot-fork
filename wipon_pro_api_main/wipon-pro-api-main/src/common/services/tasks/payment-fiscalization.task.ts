import { CACHE_MANAGER, Inject, Injectable } from '@nestjs/common';
import { Cache } from 'cache-manager';
import { sleep } from '../../utils/common';
import { v4 as uuidv4 } from 'uuid';
import { Interval } from '@nestjs/schedule';
import { FISCALIZATION_REDIS_KEY } from '../../../config/job.config';
import { createCustomLogger } from '../../logger/request-logger';
import { getManager } from 'typeorm';
import { HttpService } from '@nestjs/axios';
import { AccountTransactionDao } from '../../dao/account-transaction.dao';

const ONE_MINUTE_IN_MS = 60 * 1000;
const FISCALIZATION_API_URL = 'https://panel.bultech.kz/api/fiscalize';
const FISCALIZATION_START_DATE = '2022-12-02 00:00:00';
const WIPON_FISCALIZATION_SERVICE_ID = 3;
const WIPON_FISCALIZATION_TYPE_ID = 1;
const WIPON_FISCALIZATION_KASPI_PAYMENT_ID = 1;
const WIPON_FISCALIZATION_QIWI_PAYMENT_ID = 3;

@Injectable()
export class PaymentFiscalizationTask {
  constructor(@Inject(CACHE_MANAGER) private cacheManager: Cache, private httpService: HttpService) {}

  async generateUniqueKeyAndSetToRedis(saveKey: string) {
    const uuid = uuidv4();
    await this.cacheManager.set(saveKey, uuid, { ttl: 0 });
    await sleep(5);
    const savedUuid = await this.cacheManager.get(saveKey);
    return savedUuid == uuid;
  }

  @Interval(40 * ONE_MINUTE_IN_MS)
  async handleInterval() {
    const canContinue = await this.generateUniqueKeyAndSetToRedis(FISCALIZATION_REDIS_KEY);
    if (!canContinue) return;
    try {
      const manager = getManager();
      const results = (await manager.query(
        'select stores.buisness_bin, stores.buisness_full_legal_name, account_transactions.sum, account_transactions.id, account_transactions.provider, account_transactions.raw_info from account_transactions ' +
          'left join accounts on accounts.id = account_transactions.account_id ' +
          'left join ledgers on accounts.ledger_id = ledgers.id ' +
          'left join stores on ledgers.user_id = stores.user_id ' +
          "where account_transactions.raw_info ? 'fiscalized' = $1 and " +
          '(account_transactions.provider = $2 or account_transactions.provider = $3) and ' +
          'account_transactions.created_at > $4 and account_transactions.sum > $5',
        [false, 'kaspi', 'qiwi', FISCALIZATION_START_DATE, '0'],
      )) as Array<{
        buisness_bin: string;
        buisness_full_legal_name: string;
        sum: string;
        raw_info: any;
        id: number;
        provider: string;
      }>;

      if (results.length) {
        for (const res of results) {
          if (!res.buisness_bin || res.buisness_bin === 'null') continue;
          if (res?.raw_info?.type === 'refund' || res?.raw_info?.type === 'sub_refund') continue;
          let paymentId = WIPON_FISCALIZATION_KASPI_PAYMENT_ID;
          if (res.provider === 'qiwi') {
            paymentId = WIPON_FISCALIZATION_QIWI_PAYMENT_ID;
          }
          const payload = JSON.stringify({
            type: WIPON_FISCALIZATION_TYPE_ID,
            service: WIPON_FISCALIZATION_SERVICE_ID,
            company: {
              bin: res.buisness_bin,
              name: res.buisness_full_legal_name,
            },
            payment: {
              type: paymentId,
              sum: res.sum,
            },
          });

          await this.httpService.axiosRef.post(FISCALIZATION_API_URL, payload, {
            headers: {
              'Content-Type': 'application/json',
            },
          });

          res.raw_info.fiscalized = true;
          await manager.update(AccountTransactionDao, res.id, { raw_info: res.raw_info });
          await sleep(10);
        }
      }
    } catch (e) {
      const logger = createCustomLogger('info', 'fiscalization-errors');
      logger.log('info', {
        error: e,
      });
    } finally {
      await this.cacheManager.del(FISCALIZATION_REDIS_KEY);
    }
  }
}
