import { Body, Controller, Post, UseGuards, UseInterceptors, UsePipes, ValidationPipe } from '@nestjs/common';
import { LedgersService } from '../domain/ledgers.service';
import { PostTransferDto } from '../dto/post-transfer.dto';
import { Provider } from '../../../common/decorators/provider.decorator';
import { IpFilterGuard } from '../../../common/guards/ip-filter.guard';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiExcludeController } from '@nestjs/swagger';

@Controller('ledgers')
@UseInterceptors(TransformInterceptor)
@ApiExcludeController()
export class LedgersController {
  constructor(private readonly ledgersService: LedgersService) {}

  @Post('transfer')
  @Provider('cabinet')
  @UseGuards(IpFilterGuard)
  @UsePipes(ValidationPipe)
  async transfer(@Body() postTransferDto: PostTransferDto) {
    return await this.ledgersService.transfer(postTransferDto);
  }
}
