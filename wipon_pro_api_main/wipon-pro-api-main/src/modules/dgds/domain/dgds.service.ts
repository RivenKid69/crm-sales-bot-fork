import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DgdsRepostitory } from '../data/dgds.repostitory';

@Injectable()
export class DgdsService {
  constructor(@InjectRepository(DgdsRepostitory) private dgdsRepo: DgdsRepostitory) {}

  async getDgdsList() {
    return await this.dgdsRepo.find();
  }
}
