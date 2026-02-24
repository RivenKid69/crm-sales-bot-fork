import {
  BadRequestException,
  Body,
  Controller,
  Get,
  HttpException,
  Post,
  Query,
  UploadedFile,
  UseGuards,
  UseInterceptors,
  UsePipes,
  ValidationPipe,
} from '@nestjs/common';
import { GetUsersChecksDto } from '../dto/get-users-check.dto';
import { ChecksService } from '../domain/checks.service';
import { User } from '../../../common/decorators/user.decorator';
import { AuthGuard } from '../../auth/guard/auth.guard';
import { ValidateCheckDataDto } from '../dto/validate-check-data.dto';
import { CheckSubscriptionGuard } from '../../subscriptions/guards/check-subscription.guard';
import { StoreChecksPictureDto } from '../dto/store-checks-picture.dto';
import { FileInterceptor } from '@nestjs/platform-express';
import { UserRateLimitGuard } from '../../../common/guards/user-rate-limit.guard';
import { CheckApiKeyGuard } from '../../../common/guards/check-api-key.guard';
import { UserDao } from '../../../common/dao/user.dao';
import { FullUrl } from '../../../common/decorators/full-url.decorator';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiBearerAuth, ApiBody, ApiOkResponse, ApiOperation, ApiTags } from '@nestjs/swagger';
import { getChecksStatsResponse, paginationResponses } from '../../../common/swagger/response-examples';

@Controller('checks')
@ApiTags('checks')
@ApiBearerAuth()
@UseGuards(AuthGuard)
export class ChecksController {
  constructor(private readonly checksService: ChecksService) {}
  @Get()
  @UsePipes(ValidationPipe)
  @ApiOperation({
    summary: 'Get users checks with item products',
  })
  @ApiOkResponse({
    schema: {
      type: 'object',
      example: paginationResponses,
    },
  })
  @ApiBody({ type: GetUsersChecksDto })
  async getChecks(
    @Body() getUsersChecks: GetUsersChecksDto,
    @User() user: UserDao,
    @Query('page') page: string,
    @FullUrl() fullUrl: string,
  ) {
    return await this.checksService.getUsersCheckWithItemProducts(getUsersChecks, user.id, page, fullUrl);
  }

  @Get('stats')
  @UseInterceptors(TransformInterceptor)
  @ApiOperation({
    summary: 'Get statistic for checking items for current month',
  })
  @ApiOkResponse({
    schema: {
      type: 'object',
      example: getChecksStatsResponse,
    },
  })
  async getStats(@User() user: UserDao) {
    return await this.checksService.getChecksStats(user);
  }

  @Post()
  @UsePipes(ValidationPipe)
  @UseGuards(CheckSubscriptionGuard, UserRateLimitGuard)
  @UseInterceptors(TransformInterceptor)
  @ApiOperation({
    summary: 'Check product for originality. Must have subscription',
  })
  @ApiBody({ type: ValidateCheckDataDto })
  async validateCheckData(@Body() validateCheckData: ValidateCheckDataDto, @User() user: UserDao) {
    return await this.checksService.validateChecksData(validateCheckData, user);
  }

  @Post('subless')
  @UsePipes(ValidationPipe)
  @UseGuards(CheckApiKeyGuard)
  @UseInterceptors(TransformInterceptor)
  @ApiOperation({
    summary: 'Check product for originality without subscription. Must have API Key',
  })
  @ApiBody({ type: ValidateCheckDataDto })
  async validateCheckDataWithoutSubscription(@Body() validateCheckData: ValidateCheckDataDto, @User() user: UserDao) {
    return await this.checksService.validateChecksData(validateCheckData, user);
  }

  @Post('pict')
  @UsePipes(ValidationPipe)
  @UseInterceptors(TransformInterceptor)
  @UseInterceptors(FileInterceptor('image'))
  @ApiOperation({
    summary: 'Post picture of checking item. Body of request must have "image" field of picture',
  })
  @ApiOkResponse({
    schema: { type: 'object', example: { data: { status: 'success' } } },
  })
  @ApiBody({ type: StoreChecksPictureDto })
  async storePicture(
    @UploadedFile() image: Express.Multer.File,
    @Body() storeChecksPictureDto: StoreChecksPictureDto,
    @User() user: UserDao,
  ) {
    return await this.checksService.storeChecksPicture(storeChecksPictureDto, user, image);
  }
}
