import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { StoresRepository } from '../../data/stores.repository';
import { StoreDao } from '../../../../common/dao/store.dao';

@Injectable()
export class FindUsersStoreByUserIdAndBinUseCase {
  constructor(@InjectRepository(StoresRepository) private readonly storesRepository: StoresRepository) {}

  async handle(userId: number, bin: string): Promise<StoreDao | null> {
    const store = await this.storesRepository.findOne({ where: { user_id: userId, buisness_bin: bin } });
    if (!store) return null;
    return store;
  }
}
