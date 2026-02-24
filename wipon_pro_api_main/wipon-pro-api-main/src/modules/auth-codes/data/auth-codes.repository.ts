import { EntityRepository, Repository } from 'typeorm';
import { AuthCodeDao } from '../../../common/dao/auth-code.dao';

@EntityRepository(AuthCodeDao)
export class AuthCodesRepository extends Repository<AuthCodeDao> {
  async findUsersAuthCode(userId: number, authCode: string): Promise<AuthCodeDao | null> {
    const authCodeDao = await this.findOne({
      user_id: userId,
      code: authCode,
    });
    if (!authCodeDao) return null;
    return authCodeDao;
  }

  async findNewestUsersAuthCode(userId: number): Promise<AuthCodeDao | null> {
    const authCodeDao = await this.findOne({ order: { created_at: 'DESC' }, where: { user_id: userId } });
    if (!authCodeDao) return null;
    return authCodeDao;
  }
}
