import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { StoresRepository } from '../../data/stores.repository';
import { StoreDao } from '../../../../common/dao/store.dao';

@Injectable()
export class FindUsersStoreUseCase {
  constructor(@InjectRepository(StoresRepository) private readonly storesRepository: StoresRepository) {}

  async handle(userId: number): Promise<StoreDao | undefined> {
    return await this.storesRepository.findOne({ where: { user_id: userId } });
  }
}
