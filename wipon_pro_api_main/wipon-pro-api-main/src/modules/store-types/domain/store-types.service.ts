import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { StoreTypesRepository } from '../data/store-types.repository';

@Injectable()
export class StoreTypesService {
  constructor(@InjectRepository(StoreTypesRepository) private readonly storeTypesRepo: StoreTypesRepository) {}

  async getAllStoreTypes() {
    return await this.storeTypesRepo.find();
  }
}
