import { EntityRepository, Repository } from 'typeorm';
import { AccountDao } from '../../../common/dao/account.dao';

@EntityRepository(AccountDao)
export class AccountsRepository extends Repository<AccountDao> {}
