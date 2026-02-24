import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DgdsRepostitory } from '../../data/dgds.repostitory';
import { DgdDao } from '../../../../common/dao/dgd.dao';

@Injectable()
export class FindDgdByIdUseCase {
  constructor(@InjectRepository(DgdsRepostitory) private readonly dgdsRepo: DgdsRepostitory) {}

  async handle(id: string | number): Promise<DgdDao | undefined> {
    return await this.dgdsRepo.findOne({ where: { id } });
  }
}
