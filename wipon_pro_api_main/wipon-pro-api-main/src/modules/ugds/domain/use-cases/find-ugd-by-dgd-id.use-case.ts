import { Injectable } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { UgdsRepository } from '../../data/ugds.repository';
import { UgdDao } from '../../../../common/dao/ugd.dao';

@Injectable()
export class FindUgdByDgdIdUseCase {
  constructor(@InjectRepository(UgdsRepository) private readonly ugdsRepository: UgdsRepository) {}

  async handle(dgdId: number | string): Promise<UgdDao | null> {
    const ugd = await this.ugdsRepository.findOne({ where: { dgd_id: dgdId } });
    if (!ugd) return null;
    return ugd;
  }
}
