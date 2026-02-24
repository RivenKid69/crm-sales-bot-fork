import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DgdsRepostitory } from '../../data/dgds.repostitory';
import { DgdDao } from '../../../../common/dao/dgd.dao';

@Injectable()
export class FindDgdByNameUseCase {
  constructor(@InjectRepository(DgdsRepostitory) private readonly dgdsRepo: DgdsRepostitory) {}

  async handle(nameRu: string): Promise<DgdDao | null> {
    const dgd = await this.dgdsRepo.findOne({ where: { name_ru: nameRu } });
    if (!dgd) return null;
    return dgd;
  }
}
