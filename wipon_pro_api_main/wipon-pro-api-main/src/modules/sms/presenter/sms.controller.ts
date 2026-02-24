import { Body, Controller, Post, UseInterceptors, UsePipes, ValidationPipe } from '@nestjs/common';
import { PostCallbackDto } from '../dto/post-callback.dto';
import { SmscService } from '../domain/smsc.service';
import { TransformInterceptor } from '../../../common/interceptor/transform.interceptor';
import { ApiExcludeController } from '@nestjs/swagger';

@Controller('smsc')
@UseInterceptors(TransformInterceptor)
@ApiExcludeController()
export class SmsController {
  constructor(private readonly smscService: SmscService) {}

  @Post('callback')
  @UsePipes(ValidationPipe)
  async postCallback(@Body() postCallbackDto: PostCallbackDto) {
    return await this.smscService.postCallback(postCallbackDto);
  }
}
