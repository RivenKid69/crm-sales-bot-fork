import { Injectable, NotFoundException } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { LicensesRepository } from '../data/licenses.repository';
import { GetLicenseDto } from '../dto/get-license.dto';
import { GeoNodeDao } from '../../../common/dao/geo-node.dao';
import { In } from 'typeorm';
import { licenseResponseType } from '../../../common/types/responses/license-response.type';

@Injectable()
export class LicensesService {
  constructor(@InjectRepository(LicensesRepository) private readonly licensesRepo: LicensesRepository) {}

  async getLicense(getLicenseDto: GetLicenseDto) {
    const license = await this.licensesRepo.findOne({
      where: { license_number: getLicenseDto.license_number },
      relations: ['geoNodeLicenses'],
    });
    if (!license) {
      throw new NotFoundException({ license_number: ['License number not found'] });
    }

    const response: licenseResponseType = {
      license: {
        id: license.id,
      },
    };

    let geoNode: GeoNodeDao | null = null;
    const nodes = license.geoNodeLicenses;
    if (nodes.length) {
      const geoNodeIds = nodes.map((el) => el.geo_node_id);
      const geoNodes = await GeoNodeDao.find({ where: { id: In(geoNodeIds) }, relations: ['region'] });
      if (geoNodes.length > 1) {
        for (const node of geoNodes) {
          let isLast = false;
          geoNode = node;
          for (const child of geoNodes) {
            if (child.parent_id && child.parent_id == geoNode.id) {
              isLast = true;
              break;
            }
          }
          if (isLast) break;
        }
      } else {
        geoNode = geoNodes[0];
      }
    }

    if (geoNode) {
      const region = geoNode.region;
      response.license.region = {
        id: region.id,
        name_ru: region.name_ru,
        name_en: region.name_en,
        name_kk: region.name_kk,
      };
      response.license.city = geoNode.name_ru;
    }

    if (license.options?.Licensiat) {
      response.license.legal_name = license.options.Licensiat?.value;
    }

    if (license.options?.address) {
      response.license.address = license.options.address?.value;
    }

    let bin = license.options?.bin ? license.options.bin?.value : false;
    if (!bin) {
      bin = license.options?.iin ? license.options.iin?.value : false;
    }

    if (bin) {
      response.license.bin = bin;
    }

    return response;
  }
}
