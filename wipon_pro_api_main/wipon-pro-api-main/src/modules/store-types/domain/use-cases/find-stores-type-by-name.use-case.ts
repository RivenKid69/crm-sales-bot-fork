import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { StoreTypesRepository } from '../../data/store-types.repository';
import { StoreTypeDao } from '../../../../common/dao/store-type.dao';

@Injectable()
export class FindStoresTypeByNameUseCase {
  constructor(@InjectRepository(StoreTypesRepository) private readonly storesTypeRepository: StoreTypesRepository) {}

  async handle(nameRu: string): Promise<StoreTypeDao | undefined> {
    return await this.storesTypeRepository.findOne({ where: { name_ru: nameRu } });
  }
}
