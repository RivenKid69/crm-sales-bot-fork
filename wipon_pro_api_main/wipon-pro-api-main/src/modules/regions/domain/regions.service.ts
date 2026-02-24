import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { RegionsRepository } from '../data/regions.repository';

@Injectable()
export class RegionsService {
  constructor(@InjectRepository(RegionsRepository) private regionsRepo: RegionsRepository) {}

  getRegionsList() {
    return this.regionsRepo.find();
  }
}
