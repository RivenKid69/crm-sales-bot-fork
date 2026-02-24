import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { ExciseHashesRepository } from '../../data/excise-hashes.repository';
import { ExciseHashesDao } from '../../../../common/dao/excise-hashes.dao';

@Injectable()
export class FindOrCreateExciseHashUseCase {
  constructor(@InjectRepository(ExciseHashesRepository) private readonly exciseHashesRepo: ExciseHashesRepository) {}

  async handle(hash: string): Promise<ExciseHashesDao> {
    let exciseHash = await this.exciseHashesRepo.findOne({ hash });
    if (!exciseHash) {
      exciseHash = this.exciseHashesRepo.create({ hash });
    }
    return exciseHash;
  }
}
