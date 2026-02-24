import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ItemsRepository } from '../../data/items.repository';
import { ItemDao } from '../../../../common/dao/item.dao';

@Injectable()
export class FindOrCreateItemUseCase {
  constructor(@InjectRepository(ItemsRepository) private readonly itemsRepository: ItemsRepository) {}

  async handle(type: string, code: string): Promise<ItemDao> {
    const item = await this.itemsRepository.findOne({ [type]: code });
    if (item) return item;

    return this.itemsRepository.create({ [type]: code, created_at: new Date(), updated_at: new Date() });
  }
}
