import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { RegionsRepository } from '../../data/regions.repository';
import { RegionDao } from '../../../../common/dao/region.dao';

@Injectable()
export class FindRegionByIdUseCase {
  constructor(@InjectRepository(RegionsRepository) private readonly regionsRepo: RegionsRepository) {}

  async handle(regionId: number): Promise<RegionDao | undefined> {
    return await this.regionsRepo.findOne({ where: { id: regionId } });
  }
}
