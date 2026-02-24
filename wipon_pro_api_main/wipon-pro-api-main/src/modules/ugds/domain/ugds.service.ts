import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UgdsRepository } from '../data/ugds.repository';
import { GetUgdsListDto } from '../dto/get-ugds-list.dto';
import { UgdDao } from '../../../common/dao/ugd.dao';

@Injectable()
export class UgdsService {
  constructor(@InjectRepository(UgdsRepository) private readonly ugdsRepo: UgdsRepository) {}

  async getUgdsList(getUgdsDto: GetUgdsListDto, queryDgdId: string) {
    let ugds: UgdDao[];
    const dgdId = getUgdsDto.dgd_id ? getUgdsDto.dgd_id : queryDgdId;
    if (dgdId) {
      ugds = await this.ugdsRepo.find({ where: { dgd_id: dgdId }, relations: ['dgd'] });
    } else {
      ugds = await this.ugdsRepo.find();
    }

    return ugds;
  }
}
