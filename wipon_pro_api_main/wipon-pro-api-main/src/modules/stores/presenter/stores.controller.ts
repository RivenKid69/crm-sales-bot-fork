import { Body, Controller, Get, Post, UseGuards, UseInterceptors } from '@nestjs/common';
import { StoresService } from '../domain/stores.service';
import { User } from '../../../common/decorators/user.decorator';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { PostOrUpdateStoreDto } from '../dto/post-or-update-store.dto';
import { GetCheckDto } from '../dto/get-check.dto';
import { UserDao } from '../../../common/dao/user.dao';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { UpdateStoreAndUserNameDto } from '../dto/update-store-and-user-name.dto';
import { ApiBearerAuth, ApiBody, ApiExcludeEndpoint, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { NewFormOfSavingStoreDto } from '../dto/new-form-of-saving-store.dto';

@Controller('store')
@UseInterceptors(TransformInterceptor)
@ApiTags('store')
export class StoresController {
  constructor(private readonly storesService: StoresService) {}

  @Get()
  @UseGuards(AuthGuard)
  @ApiBearerAuth()
  @ApiOperation({
    summary: 'Get users store',
  })
  @ApiOkResponse({
    description: 'Returns users store',
  })
  async getStore(@User() user: UserDao) {
    return await this.storesService.getUsersStore(user.id);
  }

  @Post()
  @UseGuards(AuthGuard)
  // @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Create users store',
  })
  @ApiBearerAuth()
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  @ApiBody({ type: NewFormOfSavingStoreDto })
  async postOrUpdateStore(@User() user: UserDao, @Body() postOrUpdateStoreDto: PostOrUpdateStoreDto) {
    return await this.storesService.postOrUpdateStore(user.id, postOrUpdateStoreDto);
  }

  @Post('update')
  @UseGuards(AuthGuard)
  @ApiExcludeEndpoint()
  async saveOrUpdateStore(@User() user: UserDao, @Body() updateStoreAndUserNameDto: UpdateStoreAndUserNameDto) {
    return await this.storesService.updateStoreAndUserName(user, updateStoreAndUserNameDto);
  }

  @Get('check')
  // @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Check is store with license_number exists and has it active subscription',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: false } } },
  })
  @ApiBody({ type: GetCheckDto })
  async getCheck(@Body() getCheckDto: GetCheckDto) {
    return await this.storesService.getCheck(getCheckDto);
  }
}
