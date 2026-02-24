import { Controller, Get, UseInterceptors } from '@nestjs/common';
import { StoreTypesService } from '../domain/store-types.service';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';

@Controller('store-types')
@UseInterceptors(TransformInterceptor)
@ApiTags('store-types')
export class StoreTypesController {
  constructor(private readonly storeTypesService: StoreTypesService) {}

  @Get()
  @ApiOperation({
    summary: 'Get the store types list',
  })
  @ApiOkResponse({
    description: 'Returns available store types list',
  })
  async getStoreTypes() {
    return await this.storeTypesService.getAllStoreTypes();
  }
}
