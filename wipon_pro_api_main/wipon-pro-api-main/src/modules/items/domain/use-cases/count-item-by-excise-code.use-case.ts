import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ItemsRepository } from '../../data/items.repository';

@Injectable()
export class CountItemByExciseCodeUseCase {
  constructor(@InjectRepository(ItemsRepository) private readonly itemsRepository: ItemsRepository) {}

  handle(type: string, code: string): Promise<number> {
    return this.itemsRepository.count({ where: { [type]: code } });
  }
}
