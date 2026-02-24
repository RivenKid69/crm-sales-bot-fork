import { HttpException, Injectable } from '@nestjs/common';
import { PostTransferDto } from '../dto/post-transfer.dto';
import { FindUserByIdUseCase } from '../../users/domain/use-cases/find-user-by-id.use-case';
import { getManager } from 'typeorm';
import { AccountDao } from '../../../common/dao/account.dao';
import { LedgerChronicDao } from '../../../common/dao/ledger-chronic.dao';
import { greaterThan } from '../../../common/helpers/datetime';
import { BillingService } from '../../../common/services/billing/billing.service';
import createCustomErrorLogger from '../../../common/logger/error-logger';

@Injectable()
export class LedgersService {
  constructor(private readonly findUserById: FindUserByIdUseCase, private readonly billingService: BillingService) {}

  async transfer(postTransferDto: PostTransferDto) {
    const fromUser = await this.findUserById.handle(postTransferDto.from_user_id);
    const toUser = await this.findUserById.handle(postTransferDto.to_user_id);
    if (!fromUser || !fromUser.ledger)
      throw new HttpException({ from_user_id: ['The selected from user id is invalid'] }, 422);

    if (!toUser || !toUser.ledger) throw new HttpException({ to_user_id: ['The selected to user id is invalid'] }, 422);
    if (postTransferDto.from_user_id === postTransferDto.to_user_id)
      throw new HttpException({ to_user_id: ['The from user id and to user id are equal.'] }, 422);

    const fromLedger = fromUser.ledger;
    const toLedger = toUser.ledger;

    try {
      await getManager().transaction(async (transactionalEntityManager) => {
        await transactionalEntityManager.update(
          AccountDao,
          [{ ledger_id: fromLedger.id }, { ledger_id: toLedger.id }],
          {
            user_id: null,
          },
        );

        toLedger.user_id = null;
        await transactionalEntityManager.save(toLedger);
        const beginningOfTime = new Date(2017, 9, 1);
        const ledgerChronic = await LedgerChronicDao.findOne({
          where: { ledger_id: toLedger.id, user_id: toUser.id, finished_at: null },
        });

        if (ledgerChronic) {
          ledgerChronic.finished_at = new Date();
          await transactionalEntityManager.save(ledgerChronic);
        } else {
          const newLedgerChronic = new LedgerChronicDao();
          newLedgerChronic.ledger_id = toLedger.id;
          newLedgerChronic.user_id = toUser.id;
          newLedgerChronic.started_at = greaterThan(toUser.created_at, beginningOfTime)
            ? toUser.created_at
            : beginningOfTime;
          newLedgerChronic.finished_at = new Date();
          await transactionalEntityManager.save(newLedgerChronic);
        }

        const fromLedgerChronic = await LedgerChronicDao.findOne({
          where: { ledger_id: fromLedger.id, user_id: fromUser.id, finished_at: null },
        });

        if (fromLedgerChronic) {
          fromLedgerChronic.finished_at = new Date();
          await transactionalEntityManager.save(fromLedgerChronic);
        } else {
          const newFromLedgerChronic = new LedgerChronicDao();
          newFromLedgerChronic.ledger_id = fromLedger.id;
          newFromLedgerChronic.user_id = fromUser.id;
          newFromLedgerChronic.started_at = greaterThan(fromUser.created_at, beginningOfTime)
            ? fromUser.created_at
            : beginningOfTime;
          newFromLedgerChronic.finished_at = new Date();
          await transactionalEntityManager.save(newFromLedgerChronic);
        }

        fromLedger.user_id = toUser.id;
        await transactionalEntityManager.save(fromLedger);
        const lc = new LedgerChronicDao();
        lc.ledger_id = fromLedger.id;
        lc.user_id = toUser.id;
        lc.started_at = new Date();
        await transactionalEntityManager.save(lc);
        await this.billingService.createAccounts(fromUser, transactionalEntityManager);
      });
    } catch (e) {
      const errorLogger = createCustomErrorLogger();
      errorLogger.log('error', e);
      throw new HttpException({ error: 'Internal server error' }, 500);
    }
    return {
      status: 'success',
    };
  }
}
