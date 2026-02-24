import { Injectable } from '@nestjs/common';
import { AccountsRepository } from '../../data/accounts.repository';
import { InjectRepository } from '@nestjs/typeorm';
import { LessThan, MoreThan } from 'typeorm';
import { paginate } from '../../../../common/utils/common';

@Injectable()
export class FindUsersAccountsWithTransactionsUseCase {
  constructor(@InjectRepository(AccountsRepository) private readonly accountsRepo: AccountsRepository) {}

  async handle(ledgerId: number, currentPage: undefined | number, type: null | string, fullUrl: string) {
    const page = Number(currentPage) || 1;
    const perPage = 100;
    let query = await this.accountsRepo
      .createQueryBuilder('account')
      .leftJoinAndSelect('account.transactions', 'transactions')
      .where('account.ledger_id = :ledgerId', { ledgerId })
      .orderBy('transactions.created_at', 'DESC');

    if (type) {
      if (type === 'income') {
        query = query.andWhere('transactions.sum > 0');
      } else if (type === 'expense') {
        query = query.andWhere('transactions.sum < 0');
      }
    }

    const result = await query
      .skip(perPage * (page - 1))
      .take(perPage)
      .getMany();

    const data = result.reduce((accumulate, el) => {
      return [...accumulate, ...el.transactions];
    }, []);

    return paginate(data, data.length, page, perPage, fullUrl);
  }
}
